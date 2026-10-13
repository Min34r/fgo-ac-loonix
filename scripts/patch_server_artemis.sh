#!/usr/bin/env bash
# ==============================================================================
# Fate/Grand Order Arcade - Artemis Server Linux Compatibility Patcher
# Applies necessary compatibility patches to Cloud23333's Artemis server
# for modern Linux distributions (Python 3.12+ / OpenSSL / offline play).
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FGOA_ROOT="${FGOA_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
SERVER_DIR="${FGOA_ROOT}/Server"
ARTEMIS_DIR="${SERVER_DIR}/artemis"

if [ ! -d "${ARTEMIS_DIR}" ]; then
    echo "[!] Artemis directory not found at ${ARTEMIS_DIR}. Skipping."
    exit 0
fi

echo "============================================================"
echo " Artemis Server Linux Compatibility Patcher"
echo " Target: ${ARTEMIS_DIR}"
echo "============================================================"

# 1. Remove deprecated ssl_version=3 from index.py (fixes Python 3.12+ crash)
INDEX_PY="${ARTEMIS_DIR}/index.py"
if [ -f "${INDEX_PY}" ]; then
    if grep -q "ssl_version=3" "${INDEX_PY}" 2>/dev/null; then
        echo "[PATCH] Removing obsolete ssl_version=3 from index.py..."
        sed -i '/ssl_version=3/d' "${INDEX_PY}"
        echo "  [OK] index.py patched for Python 3.12+ compatibility."
    else
        echo "  [OK] index.py does not contain ssl_version=3."
    fi
fi

# 2. Ensure native MariaDB cnf exists
CNF_FILE="${SERVER_DIR}/mariadb_native.cnf"
if [ ! -f "${CNF_FILE}" ]; then
    echo "[CONFIG] Generating native MariaDB configuration..."
    DATA_DIR="${SERVER_DIR}/data/mariadb"
    STATE_DIR="${SERVER_DIR}/state"
    mkdir -p "${STATE_DIR}" "${SERVER_DIR}/logs"
    cat <<EOF > "${CNF_FILE}"
[mariadbd]
datadir=${DATA_DIR}
port=3307
bind-address=127.0.0.1
socket=${STATE_DIR}/mariadb.sock
skip-name-resolve
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
max_connections=50
max_allowed_packet=64M
performance_schema=OFF
skip-log-bin
innodb_flush_log_at_trx_commit=2
sync_binlog=0
log-error=${STATE_DIR}/mariadb_native.log
pid-file=${STATE_DIR}/mariadb_native.pid

[client]
host=127.0.0.1
port=3307
socket=${STATE_DIR}/mariadb.sock
default-character-set=utf8mb4
EOF
    echo "  [OK] Generated ${CNF_FILE}."
fi

# 3. Copy start/stop native server scripts into Server/
if [ -f "${SCRIPT_DIR}/start_server_native.sh" ]; then
    cp -f "${SCRIPT_DIR}/start_server_native.sh" "${SERVER_DIR}/start_server_native.sh" 2>/dev/null || true
    chmod +x "${SERVER_DIR}/start_server_native.sh" 2>/dev/null || true
fi
if [ -f "${SCRIPT_DIR}/stop_server_native.sh" ]; then
    cp -f "${SCRIPT_DIR}/stop_server_native.sh" "${SERVER_DIR}/stop_server_native.sh" 2>/dev/null || true
    chmod +x "${SERVER_DIR}/stop_server_native.sh" 2>/dev/null || true
fi

# 4. Synchronize version configuration (11.00 vs 11.51) and clean up obsolete components
FGO_YAML="${ARTEMIS_DIR}/config/fgo.yaml"
AUX_JSON="${FGOA_ROOT}/GameData/SDEJ/amdaemon_aux.json"

if [ -d "${FGOA_ROOT}/DEVICE/print/FGO11_51_AllServants" ] || [ -d "${FGOA_ROOT}/App/Localization" ]; then
    echo "[VERSION] Detected 11.51 (V1.10) game files. Ensuring 11.51 server & data configuration..."
    if [ -f "${FGO_YAML}" ]; then
        sed -i 's/advertise_version: *[0-9]*/advertise_version: 1151/g' "${FGO_YAML}" 2>/dev/null || true
    fi
    if [ -f "${AUX_JSON}" ]; then
        sed -i 's/"develop_version": *"[^"]*"/"develop_version": "11.51"/g' "${AUX_JSON}" 2>/dev/null || true
    fi
    if [ -f "${FGOA_ROOT}/App/deck.json" ]; then
        sed -i 's/FGO11_AllServants/FGO11_51_AllServants/g' "${FGOA_ROOT}/App/deck.json" 2>/dev/null || true
    fi
    # Clean obsolete 11.00 files replaced by 11.51
    rm -rf "${FGOA_ROOT}/App/ICF1" "${FGOA_ROOT}/App/ICF2" \
           "${FGOA_ROOT}/App/EasterEgg" "${FGOA_ROOT}/App/BGM" \
           "${FGOA_ROOT}/App/FGOAudio.dll" "${FGOA_ROOT}/App/FgoDlss.dll" 2>/dev/null || true
    if [ -d "${FGOA_ROOT}/App/Localization/zh" ] && [ -d "${FGOA_ROOT}/App/zh" ]; then
        rm -rf "${FGOA_ROOT}/App/zh" 2>/dev/null || true
    fi
    echo "  [OK] Server advertise_version set to 1151 and obsolete 11.00 files cleaned."
fi

echo "[DONE] Artemis server Linux compatibility verification complete."

#!/bin/bash
# ==============================================================================
# Fate/Grand Order Arcade - Native Linux Server Stack Launcher
# Orchestrates embedded MariaDB (port 3307) and Artemis server (ports 8777, 8443, 22345).
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Check if running inside Server/ or scripts/
if [ -d "$SCRIPT_DIR/artemis" ]; then
    SERVER_DIR="$SCRIPT_DIR"
else
    SERVER_DIR="$(cd "$SCRIPT_DIR/../Server" 2>/dev/null && pwd || true)"
fi

if [ -z "$SERVER_DIR" ] || [ ! -d "$SERVER_DIR/artemis" ]; then
    echo "[Server] ERROR: Could not locate Artemis server directory." >&2
    exit 1
fi

STATE_DIR="$SERVER_DIR/state"
LOGS_DIR="$SERVER_DIR/logs"
DATA_DIR="$SERVER_DIR/data/mariadb"
mkdir -p "$STATE_DIR" "$LOGS_DIR"

# Python interpreter selection
if [ -f "$SERVER_DIR/artemis/.venv/bin/python" ]; then
    VENV="$SERVER_DIR/artemis/.venv/bin/python"
else
    VENV="python3"
fi

# Ensure MariaDB config exists with correct dynamic paths
CNF_FILE="$SERVER_DIR/mariadb_native.cnf"
if [ ! -f "$CNF_FILE" ]; then
    echo "[Server] Generating dynamic MariaDB configuration: $CNF_FILE"
    cat <<EOF > "$CNF_FILE"
[mariadbd]
datadir=$DATA_DIR
port=3307
bind-address=127.0.0.1
socket=$STATE_DIR/mariadb.sock
skip-name-resolve
character-set-server=utf8mb4
collation-server=utf8mb4_unicode_ci
max_connections=50
max_allowed_packet=64M
performance_schema=OFF
skip-log-bin
innodb_flush_log_at_trx_commit=2
sync_binlog=0
log-error=$STATE_DIR/mariadb_native.log
pid-file=$STATE_DIR/mariadb_native.pid

[client]
host=127.0.0.1
port=3307
socket=$STATE_DIR/mariadb.sock
default-character-set=utf8mb4
EOF
fi

# Handle --host parameter
HOST_MODE="auto"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_MODE="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Apply host config if helper exists
if [ -f "$SERVER_DIR/tools/fgo_server_config.py" ]; then
    CURRENT_HOST=$("$VENV" "$SERVER_DIR/tools/fgo_server_config.py" show 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('address',''))" 2>/dev/null || true)
    EXPECTED_HOST="192.168.100.1"
    if [ "$HOST_MODE" != "auto" ]; then
        EXPECTED_HOST="$HOST_MODE"
    fi
    if [ "$EXPECTED_HOST" != "$CURRENT_HOST" ]; then
        echo "[Server] Applying host config: $CURRENT_HOST -> $EXPECTED_HOST"
        "$VENV" "$SERVER_DIR/tools/fgo_server_config.py" apply --host "$HOST_MODE" >/dev/null 2>&1 || \
            echo "[Server] WARNING: Config apply failed, using existing configs." >&2
    fi
fi

# 1. Start MariaDB if not listening on 3307
if ! ss -tulpn 2>/dev/null | grep -q ":3307\b"; then
    echo "[Server] Starting native MariaDB on port 3307..."
    setsid mariadbd --defaults-file="$CNF_FILE" </dev/null >/dev/null 2>&1 &
    sleep 2
    if ! ss -tulpn 2>/dev/null | grep -q ":3307\b"; then
        echo "[Server] ERROR: Failed to start MariaDB." >&2
        exit 1
    fi
    echo "[Server] MariaDB listening on 127.0.0.1:3307."
else
    echo "[Server] MariaDB already running on port 3307."
fi

# 2. Start Artemis HTTP/Billing/AimeDB if not listening on 8777
if ! ss -tulpn 2>/dev/null | grep -q ":8777\b"; then
    echo "[Server] Starting native Artemis on port 8777..."
    cd "$SERVER_DIR/artemis"
    setsid "$VENV" index.py --config config </dev/null >> "$LOGS_DIR/artemis.log" 2>&1 &
    echo $! > "$STATE_DIR/artemis.pid"

    for i in {1..10}; do
        if ss -tulpn 2>/dev/null | grep -q ":8777\b"; then
            break
        fi
        sleep 1
    done

    if ! ss -tulpn 2>/dev/null | grep -q ":8777\b"; then
        echo "[Server] ERROR: Failed to start Artemis." >&2
        exit 1
    fi
    echo "[Server] Artemis listening on ports 8777, 8443, 22345."
else
    echo "[Server] Artemis already running on port 8777."
fi

echo "[Server] Local server stack is up and running!"

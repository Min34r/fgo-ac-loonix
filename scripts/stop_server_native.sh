#!/bin/bash
# ==============================================================================
# Fate/Grand Order Arcade - Native Server Stack Stopper
# Stops running Artemis and MariaDB instances safely.
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/artemis" ]; then
    SERVER_DIR="$SCRIPT_DIR"
else
    SERVER_DIR="$(cd "$SCRIPT_DIR/../Server" 2>/dev/null && pwd || true)"
fi

echo "[Server] Stopping Artemis..."
if [ -n "$SERVER_DIR" ] && [ -f "$SERVER_DIR/state/artemis.pid" ]; then
    kill "$(cat "$SERVER_DIR/state/artemis.pid")" 2>/dev/null || true
    rm -f "$SERVER_DIR/state/artemis.pid"
fi
pkill -f "artemis.*index.py" 2>/dev/null || true

echo "[Server] Stopping MariaDB..."
if [ -n "$SERVER_DIR" ] && [ -f "$SERVER_DIR/state/mariadb_native.pid" ]; then
    kill "$(cat "$SERVER_DIR/state/mariadb_native.pid")" 2>/dev/null || true
    rm -f "$SERVER_DIR/state/mariadb_native.pid"
fi
pkill -f "mariadbd.*mariadb_native.cnf" 2>/dev/null || true

echo "[Server] Native server stack stopped."

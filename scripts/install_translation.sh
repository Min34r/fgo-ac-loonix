#!/usr/bin/env bash
# ==============================================================================
# Fate/Grand Order Arcade - English Translation Downloader & Installer
# Fetches the verified Scooby v1.1.2 translation payload from GitHub and deploys
# it into App/zh.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FGOA_ROOT="${FGOA_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"

DOWNLOAD_DIR="${FGOA_ROOT}/scratch/downloads"
mkdir -p "${DOWNLOAD_DIR}"

ZIP_NAME="FGOAC-scooby-v1.1.2.zip"
ZIP_PATH="${DOWNLOAD_DIR}/${ZIP_NAME}"
DOWNLOAD_URL="https://github.com/githubuser420x/FGOAC-scooby/releases/download/v1.1.2/FGOAC-scooby-v1.1.2.zip"
EXPECTED_SHA256="76dab15be143f600f34823df0988228a409c1b821d70d8a26343ef18e23ed3a3"

echo "============================================================"
echo " Fate/Grand Order Arcade - English Translation Installer"
echo "============================================================"
echo "Target Installation: ${FGOA_ROOT}"
echo ""

# 1. Download
if [ -f "${ZIP_PATH}" ]; then
    CURRENT_HASH=$(sha256sum "${ZIP_PATH}" | awk '{print $1}')
    if [ "${CURRENT_HASH}" = "${EXPECTED_SHA256}" ]; then
        echo "[OK] Complete release zip already exists and verified."
    else
        echo "[INFO] Incomplete/invalid zip found. Downloading full release..."
        curl -L --retry 5 --retry-delay 2 -o "${ZIP_PATH}" "${DOWNLOAD_URL}"
    fi
else
    echo "[INFO] Downloading ${ZIP_NAME} from GitHub..."
    curl -L --retry 5 --retry-delay 2 -o "${ZIP_PATH}" "${DOWNLOAD_URL}"
fi

# 2. Checksum Verification
echo "[INFO] Verifying SHA256 checksum..."
ACTUAL_HASH=$(sha256sum "${ZIP_PATH}" | awk '{print $1}')
if [ "${ACTUAL_HASH}" != "${EXPECTED_SHA256}" ]; then
    echo "[ERROR] Checksum mismatch! Expected ${EXPECTED_SHA256}, got ${ACTUAL_HASH}."
    exit 1
fi
echo "[OK] Checksum verified: ${ACTUAL_HASH}"

# 3. Extract payload into App/zh
TEMP_EXTRACT="${FGOA_ROOT}/scratch/en_patch_temp"
mkdir -p "${TEMP_EXTRACT}"
rm -rf "${TEMP_EXTRACT:?}"/*

echo "[INFO] Extracting translation payload..."
unzip -q -o "${ZIP_PATH}" "payload/*" -d "${TEMP_EXTRACT}"

mkdir -p "${FGOA_ROOT}/App/zh"
cp -r "${TEMP_EXTRACT}/payload/App/zh/"* "${FGOA_ROOT}/App/zh/"

if [ -f "${TEMP_EXTRACT}/payload/Server/artemis/titles/fgo/data/summon_candidates.json" ]; then
    mkdir -p "${FGOA_ROOT}/Server/artemis/titles/fgo/data"
    cp -f "${TEMP_EXTRACT}/payload/Server/artemis/titles/fgo/data/summon_candidates.json" \
          "${FGOA_ROOT}/Server/artemis/titles/fgo/data/summon_candidates.json"
fi

rm -rf "${TEMP_EXTRACT}"

# 4. Enable in fgo-launcher.json if present
if [ -f "${FGOA_ROOT}/App/fgo-launcher.json" ]; then
    sed -i 's/"chineseEnabled": false/"chineseEnabled": true/g' "${FGOA_ROOT}/App/fgo-launcher.json" 2>/dev/null || true
fi

echo ""
echo "============================================================"
echo " [SUCCESS] English translation successfully installed into App/zh!"
echo "============================================================"

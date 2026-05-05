#!/usr/bin/env bash
# scripts/download_atlas.sh
#
# Pull ATLAS (Alsaheel et al., USENIX Security '21) raw audit logs from
# https://github.com/purseclab/ATLAS into data/raw/atlas/.
#
# Idempotent: skips download if all 10 scenarios are already present.
# Force re-download by removing data/raw/atlas/ first.

set -euo pipefail

REPO_URL="https://github.com/purseclab/ATLAS.git"
SCENARIOS=(S1 S2 S3 S4 M1 M2 M3 M4 M5 M6)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${PROJECT_ROOT}/data/raw/atlas"
TMP_DIR="$(mktemp -d -t atlas-download-XXXXXX)"

cleanup() { rm -rf "${TMP_DIR}"; }
trap cleanup EXIT

mkdir -p "${DATA_DIR}"

# Fast path: skip if every scenario already has a logs/ folder.
all_present=true
for s in "${SCENARIOS[@]}"; do
    if [[ ! -d "${DATA_DIR}/${s}/logs" ]]; then
        all_present=false
        break
    fi
done

if [[ "${all_present}" == "true" ]]; then
    echo "[download_atlas] All ${#SCENARIOS[@]} scenarios present at ${DATA_DIR}; nothing to do."
    echo "[download_atlas] Force re-download by removing ${DATA_DIR} first."
    exit 0
fi

echo "[download_atlas] Cloning ${REPO_URL} (shallow) into ${TMP_DIR} ..."
git clone --depth 1 "${REPO_URL}" "${TMP_DIR}" >/dev/null

echo "[download_atlas] Extracting raw_logs/*.zip to ${DATA_DIR} ..."
for s in "${SCENARIOS[@]}"; do
    zip_path="${TMP_DIR}/raw_logs/${s}.zip"
    if [[ ! -f "${zip_path}" ]]; then
        echo "[download_atlas] FATAL: expected ${zip_path} not found in cloned repo." >&2
        exit 1
    fi
    echo "[download_atlas]  -> ${s}"
    unzip -oq "${zip_path}" -d "${DATA_DIR}"
done

echo "[download_atlas] Done. Run 'python scripts/verify_data_integrity.py' next to build the manifest."

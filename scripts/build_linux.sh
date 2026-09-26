#!/usr/bin/env bash
set -euo pipefail

echo "==> Building AGY2API for Linux..."

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 1. Build frontend UI
if [ -d "ui" ]; then
    echo "==> Building UI..."
    cd ui
    npm ci || npm install
    npm run build
    cd "$ROOT_DIR"
fi

# 2. Install dependencies
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller

# 3. Build single-file binary with PyInstaller
echo "==> Running PyInstaller for Linux..."
pyinstaller --clean --noconfirm agy2api.spec

if [ -f "dist/agy2api" ]; then
    ARCH="$(uname -m)"
    mv "dist/agy2api" "dist/agy2api-linux-${ARCH}"
    chmod +x "dist/agy2api-linux-${ARCH}"
    echo "==> Successfully created dist/agy2api-linux-${ARCH}"
fi

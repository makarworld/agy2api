#!/bin/bash
set -e

# Build the UI
echo "Building UI..."
cd ui
npm run build
cd ..

# Start FastAPI
echo "Starting FastAPI on port 8000..."
source .venv/bin/activate
uvicorn app.main:app --reload

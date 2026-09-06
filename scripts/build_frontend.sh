#!/usr/bin/env bash
# Build the owner dashboard SPA into frontend/dist so the FastAPI server can
# serve it. Requires Node.js 20+.
set -euo pipefail

cd "$(dirname "$0")/../frontend"
if [ ! -d node_modules ]; then
  npm ci
fi
npm run build
echo "Frontend built: $(pwd)/dist"
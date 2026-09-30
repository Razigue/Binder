#!/usr/bin/env bash
# Construit l'application de bureau : packaging/dist/Binder/Binder
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Interface"
(cd ../frontend && npm ci --silent && npm run build)

echo "==> Exécutable"
cd ../backend
uv sync --extra desktop --quiet
uv run pyinstaller ../packaging/binder.spec --noconfirm \
  --distpath ../packaging/dist --workpath ../packaging/build

echo "OK : packaging/dist/Binder/Binder"

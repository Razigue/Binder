#!/usr/bin/env bash
# Construit l'application de bureau (Linux, macOS). Sous Windows : python packaging\build.py
set -euo pipefail
exec python3 "$(dirname "$0")/build.py" "$@"

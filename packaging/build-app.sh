#!/usr/bin/env bash
# Builds the desktop application (Linux, macOS). On Windows: python packaging\build.py
set -euo pipefail
exec python3 "$(dirname "$0")/build.py" "$@"

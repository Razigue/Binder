#!/usr/bin/env bash
# Installs Binder for the current user (no sudo) and adds it to the applications menu.
# Uninstall: ./install-linux.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"

PREFIX="$HOME/.local/opt/binder"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -rf "$PREFIX" "$APPS/binder.desktop" "$ICONS/binder.png"
  echo "Binder uninstalled. Your data stays in ~/.local/share/binder."
  exit 0
fi

[[ -x dist/Binder/Binder ]] || { echo "Run ./build-app.sh first"; exit 1; }

rm -rf "$PREFIX" && mkdir -p "$PREFIX" "$APPS" "$ICONS"
cp -r dist/Binder/. "$PREFIX/"
cp binder.png "$ICONS/binder.png"
sed "s#@BINDER_BIN@#$PREFIX/Binder#" binder.desktop > "$APPS/binder.desktop"
chmod +x "$APPS/binder.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "Binder installed: look for \"Binder\" in your applications."

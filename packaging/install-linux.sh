#!/usr/bin/env bash
# Installe Binder pour l'utilisateur courant (sans sudo) et l'ajoute au menu des applications.
# Désinstaller : ./install-linux.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")"

PREFIX="$HOME/.local/opt/binder"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -rf "$PREFIX" "$APPS/binder.desktop" "$ICONS/binder.png"
  echo "Binder désinstallé. Vos données restent dans ~/.local/share/binder."
  exit 0
fi

[[ -x dist/Binder/Binder ]] || { echo "Lancez d'abord ./build-app.sh"; exit 1; }

rm -rf "$PREFIX" && mkdir -p "$PREFIX" "$APPS" "$ICONS"
cp -r dist/Binder/. "$PREFIX/"
cp binder.png "$ICONS/binder.png"
sed "s#@BINDER_BIN@#$PREFIX/Binder#" binder.desktop > "$APPS/binder.desktop"
chmod +x "$APPS/binder.desktop"
update-desktop-database "$APPS" 2>/dev/null || true
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
echo "Binder installé : cherchez « Binder » dans vos applications."
